"""
author: ljk
email: chaoyuemyself@hotmail.com
"""
import pymysql
import warnings
import queue
from sys import exit

warnings.filterwarnings('error', category=pymysql.err.Warning)


class ImprovedDb(object):
    """
    A improved database class based PyMySQL.
    db_config: database config information, should be a dict
    pool: if use connection pool
    pool_init_size: init number of connection pool
    """
    def __init__(self, db_config, pool=False, pool_init_size=10):
        self.db_config = db_config
        if pool:
            self.pool_init_size = pool_init_size
            self.pool_max_size = pool_max_size
            self.pool = queue.Queue()

    def connect(self, recreate=False):
        """
        Create and return a MySQL connection object.
        err_exit: if exit when occur Exception(single-thread mode use)
        recreate: just a flag can show more information,
                  indicate if the 'create connection' action due to lack of useable connection in the pool
        """
        if recreate: print('Warning: Create a new connection')
        try:
            connection = pymysql.connect(**self.db_config)
            return connection
        except Exception:
            raise

    @staticmethod
    def create_cursor(connection, dictcursor=False):
        """
        Return the given connection's cursor.
        dictcursor: cursor type is tuple(default) or dict
        """
        cur = connection.cursor() if not dictcursor else connection.cursor(pymysql.cursors.DictCursor)
        return cur

    @staticmethod
    def execute_query(cursor, query, args=(), return_one=False, exec_many=False):
        """
        A higher level implementation for execute query.
        cursor: cursor object of a connection
        return_one: whether want only one row of the result
        exec_many: whether use pymysql's executemany() method
        """
        try:
            if exec_many:
                cursor.executemany(query, args)
            else:
                cursor.execute(query, args)
        except Exception:
            raise
        res = cursor.fetchall()
        # if no record match the query, return () if return_one==False, else return None
        return (res[0] if res else None) if return_one else res

    def execute_query_multiplex(self, connection, query, args=(), dictcursor=False, return_one=False, exec_many=False):
        """
        A convenience method for:
                connection = self.connect()
                cursor = self.create_cursor(connection)
                self.execute_query(cursor, query, args=())
                cursor.close()
                self.pool_put_connection(connection)
        connection: connection object
        dictcursor: cursor type is tuple(default) or dict
        return_one: whether want only one row of the result
        exec_many: whether use pymysql's executemany() method
        """
        with connection.cursor() if not dictcursor else connection.cursor(pymysql.cursors.DictCursor) as cursor:
            try:
                if exec_many:
                    cursor.executemany(query, args)
                else:
                    cursor.execute(query, args)
            except Exception:
                raise
            res = cursor.fetchall()
            print('multiplex: ', cursor.connection)
            # return connection back to the pool
            self.pool_put_connection(connection)
        return (res[0] if res else None) if return_one else res

    def create_pool(self):
        """
        Create specified number of connections when create the pool.
        The number is the smaller of self.pool_init_size and self.pool_max_size else.
        """
        for i in range(self.pool_init_size if self.pool_init_size < self.pool_max_size else self.pool_max_size):
            conn = self.connect()
            self.pool.put(conn)

    def pool_get_connection(self, timeout=10):
        """
        Multi-thread mode, sub-thread should get a connection object from the pool.
        If a sub-thread can't get a connection object, then re-create a fixed number of connections
        (use the smaller of self.pool_init_size and self.pool_max_size), and put them into the pool.
        timeout: timeout when get connection object from the pool.
        """
        try:
            conn = self.pool.get(timeout=timeout)
        except queue.Empty:
            '''create new connection at the reason of lack of pool'''
            for i in range(self.pool_init_size if self.pool_init_size < self.pool_max_size else self.pool_max_size):
                try:
                    self.pool_put_connection(self.connect(recreate=True), conn_type='new')
                except Exception as err:
                    '''catch Exception of self.connect() method'''
                    print('Error: during create new connection\n{}{}'.format(''*6, err))
                    break
            raise Exception("cat't get connection from pool")
        # caller should the take care of the availability of the connection object from the pool
        return conn

    def pool_put_connection(self, connection, conn_type='old'):
        """
        Before the sub-thread end, should return the connection object back to the pool
        conn_type: "new" or "old"(default) just a flag can show more information
        """
        try:
            self.pool.put_nowait(connection)
        except queue.Full:
            if conn_type == 'new':
                print("Warning: Can't put new connection to pool")
            else:
                print("Warning: Can't put connection back to pool")

    @staticmethod
    def db_close(connection):
        connection.close()