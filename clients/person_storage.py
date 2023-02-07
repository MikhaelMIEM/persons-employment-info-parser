from abc import ABC, abstractmethod
from string import Template
from typing import List
from itertools import product

import psycopg2

from persons_employment_info_extractor.domain import TextPersonInfo


class PersonStorage(ABC):
    @abstractmethod
    def push_person_info(self, info: TextPersonInfo) -> None:
        pass

class PersonStoragePostgres(PersonStorage):
    def __init__(self, database: str, user: str, password: str, host: str = '127.0.0.1', port: int = 5432):
        self.conn = psycopg2.connect(database=database, user=user, password=password, host=host, port=port)
        self.cur = self.conn.cursor()
        self.__prepare()

    def __del__(self):
        self.conn.close()
        self.cur.close()

    def __prepare(self):
        create_person_table = """
        create table if not exists Person (
            id serial primary key,
            norm_name text not null,
            unique (norm_name)
        );
        """
        create_company_table = """
        create table if not exists Company (
            id serial primary key,
            norm_name text not null,
            unique (norm_name)
        )        
        """
        create_job_table = """
        create table if not exists Job (
            id serial primary key,
            norm_name text not null,
            unique (norm_name)
        )        
        """
        create_work_table = """
        create table if not exists Work (
            id serial primary key,
            person integer references Person,
            company integer references Company,
            job integer references Job,
            unique(person, company, job)
        )        
        """
        self.cur.execute(create_person_table)
        self.cur.execute(create_company_table)
        self.cur.execute(create_job_table)
        self.cur.execute(create_work_table)
        self.conn.commit()

    def push_person_info(self, info: List[TextPersonInfo]) -> None:
        insert_person = Template(
            """
            insert into Person (norm_name) values ('${norm_name}') on conflict do nothing
            """
        )
        insert_company = Template(
            """
            insert into Company (norm_name) values ('${norm_name}') on conflict do nothing
            """
        )
        insert_job = Template(
            """
            insert into Job (norm_name) values ('${norm_name}') on conflict do nothing
            """
        )
        insert_work = Template(
            """
            insert into Work (person, company, job) values (${person}, ${company}, ${job}) on conflict do nothing
            """
        )

        def __get_ids_by_names(table: str, names: List[str]) -> List[str]:
            if not names:
                return []
            names_req_list = (f"'{name}'" for name in names)
            names_req_list = f"({', '.join(names_req_list)})"
            request = f'select id from {table} where norm_name in {names_req_list}'
            self.cur.execute(request)
            return [row[0] for row in self.cur.fetchall()]

        for person_info in info:
            self.cur.execute(insert_person.substitute(norm_name=person_info.norm_name))
            for job in person_info.jobs_norm_names:
                self.cur.execute(insert_job.substitute(norm_name=job))
            for company in person_info.companies_norm_names:
                self.cur.execute(insert_company.substitute(norm_name=company))
            self.conn.commit()
            person_id = __get_ids_by_names("Person", [person_info.norm_name])[0]
            for work in person_info.work:
                job_ids = __get_ids_by_names("Job", work.jobs_norm_names) or ['null']
                company_ids = __get_ids_by_names("Company", work.companies_norm_names) or ['null']
                if ['null'] == job_ids == company_ids:
                    continue
                for (job_id, company_id) in product(job_ids, company_ids):
                    self.cur.execute(insert_work.substitute(person=person_id, company=company_id, job=job_id))
                    self.conn.commit()
