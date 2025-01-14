import psycopg
from asyncio import gather


class AcceptedTables:
    async def accept_work(self, mentor_id, work_id):
        """
        Moves a line from COURSE_WORKS to ACCEPTED table, increments LOAD
        column in MENTORS table and appends ID into COURSE_WORKS column
        Does nothing if a line exists

        Parameters
        ----------
        mentor_id : int
            database id of the mentor
        work_id : int
            database id of the course work

        Raises
        ------
        DBAccessError whatever
        DBDoesNotExist
        DBAlreadyExists
        """
        if self.db is None:
            self.db = await psycopg.AsyncConnection.connect(self.conn_opts)
        line = await (await self.db.execute('SELECT * FROM COURSE_WORKS '
                                            'WHERE ID = %s', (work_id,))).fetchone()
        if line is None:
            return
        to_delete = await (await self.db.execute('SELECT ID FROM COURSE_WORKS '
                                                 'WHERE STUDENT = %s', (line[1],))).fetchall()
        to_delete.remove((line[0],))
        cw_subj = await (await self.db.execute('SELECT SUBJECT FROM COURSE_WORKS_SUBJECTS '
                                               'WHERE COURSE_WORK = %s', (work_id,))).fetchall()
        await gather(self.db.execute('INSERT INTO ACCEPTED VALUES('
                                     '%s, %s, %s) '
                                     'ON CONFLICT (STUDENT) DO NOTHING',
                                     (line[0], line[1], line[2],)),
                                     # id      student  description
                     *[self.db.execute('INSERT INTO ACCEPTED_SUBJECTS VALUES('
                                       '%s, %s) ON CONFLICT DO NOTHING',
                                       (work_id, subj,))
                       for (subj,) in cw_subj],
                     self.remove_course_work(line[0]),
                     self.db.execute('UPDATE MENTORS SET LOAD = LOAD + 1 '
                                     'WHERE ID = %s', (mentor_id,)),
                     self.db.execute('INSERT INTO MENTORS_STUDENTS VALUES('
                                     '%s, %s)', (mentor_id, line[1],)),
                     *[self.db.execute('DELETE FROM COURSE_WORKS_SUBJECTS '
                                       'WHERE COURSE_WORK = %s', (id_f,))
                       for (id_f,) in to_delete],
                     *[self.db.execute('DELETE FROM COURSE_WORKS '
                                       'WHERE ID = %s', (id_f,))
                       for (id_f,) in to_delete])
        await self.db.commit()

    async def reject_work(self, mentor_id, work_id):
        """
        Disown a student

        Moves a line from ACCEPTED to COURSE_WORK table, decrements LOAD
        column in MENTORS table and subtracts ID from COURSE_WORKS column
        Does nothing if a line does not exist

        Parameters
        ----------
        mentor_id : int
            database id of the mentor
        work_id : int
            database id of the course work

        Raises
        ------
        DBAccessError whatever
        DBDoesNotExist
        DBAlreadyExists
        """
        if self.db is None:
            self.db = await psycopg.AsyncConnection.connect(self.conn_opts)
        line = await (await self.db.execute('SELECT * FROM ACCEPTED '
                                            'WHERE ID = %s', (work_id,))).fetchone()
        cw_subj = await (await self.db.execute('SELECT SUBJECT FROM ACCEPTED_SUBJECTS '
                                               'WHERE COURSE_WORK = %s', (work_id,))).fetchall() 
        if line is None:
            return
        await gather(self.db.execute('INSERT INTO COURSE_WORKS VALUES('
                                     '%s, %s, %s)',
                                     (line[0], line[1], line[2],)),
                     #                id      student  description
                     *[self.db.execute('INSERT INTO COURSE_WORKS_SUBJECTS VALUES('
                                       '%s, %s) ON CONFLICT DO NOTHING',
                                       (work_id, subj))
                       for (subj,) in cw_subj],
                     self.db.execute('DELETE FROM ACCEPTED_SUBJECTS '
                                     'WHERE COURSE_WORK = %s', (work_id,)),
                     self.db.execute('DELETE FROM ACCEPTED '
                                     'WHERE ID = %s', (work_id,)),
                     self.db.execute('UPDATE MENTORS SET LOAD = LOAD + 1 '
                                     'WHERE ID = %s', (mentor_id,)),
                     self.db.execute('DELETE FROM MENTORS_STUDENTS '
                                     'WHERE MENTOR = %s AND '
                                     'STUDENT = %s', (mentor_id, line[1],)))
        await self.db.commit()

    async def readmission_work(self, work_id):
        """
        Copies a line from ACCEPTED table to COURSE_WORKS table

        Parameters
        ----------
        work_id : int
            database id of the course work

        Raises
        ------
        DBAccessError whatever
        DBDoesNotExist
        DBAlreadyExists
        """
        if self.db is None:
            self.db = await psycopg.AsyncConnection.connect(self.conn_opts)
        line = await (await self.db.execute('SELECT * FROM ACCEPTED '
                                            'WHERE ID = %s', (work_id,))).fetchone()
        await self.db.execute('INSERT INTO COURSE_WORKS VALUES('
                              '%s, %s, %s)',
                              (line[0], line[1], line[2],))
        await self.db.commit()

    async def get_accepted(self, id_field=None, subjects=[], student=None):
        if self.db is None:
            self.db = await psycopg.AsyncConnection.connect(self.conn_opts)
        if id_field is not None:
            res = [await (await self.db.execute('SELECT * FROM ACCEPTED'
                                                'WHERE ID = %s', (id_field,))).fetchone()]
            return await self.assemble_courses_dict(res)
        if subjects:
            ids = [cur for (cur,) in
                   await (await self.db.execute('SELECT COURSE_WORK FROM COURSE_WORKS_SUBJECTS '
                                                'WHERE SUBJECT = ANY(%s)', tuple(subjects))).fetchall()]
            works = [await (await self.db.execute('SELECT * FROM ACCEPTED '
                                                  'WHERE ID = %s', (id_f,))).fetchone()
                     for id_f in ids]
            return await self.assemble_courses_dict(works)
        if student is not None:
            res = await (await self.db.execute('SELECT * FROM ACCEPTED '
                                               'WHERE STUDENT = %s',
                                               (student,))).fetchall()
            return await self.assemble_courses_dict(res)
        res = await (await self.db.execute('SELECT * FROM ACCEPTED')).fetchall()
        return await self.assemble_courses_dict(res)
