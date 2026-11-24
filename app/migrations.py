from sqlalchemy import inspect


def upgrade_sqlite_schema(engine):
    """Add duration snapshots and patient visibility to existing local databases."""
    additions = {
        'doctor': {'duration_minutes':'INTEGER NOT NULL DEFAULT 60','active':'BOOLEAN NOT NULL DEFAULT 1','settings_version':'INTEGER NOT NULL DEFAULT 0'},
        'user': {'demo_doctor':'BOOLEAN NOT NULL DEFAULT 0','enabled':'BOOLEAN NOT NULL DEFAULT 1','auth_version':'INTEGER NOT NULL DEFAULT 0'},
        'appointment': {'duration_minutes':'INTEGER NOT NULL DEFAULT 60',
                        'patient_hidden':'BOOLEAN NOT NULL DEFAULT 0','version':'INTEGER NOT NULL DEFAULT 0'},
    }
    with engine.begin() as connection:
        connection.exec_driver_sql('BEGIN IMMEDIATE')
        for table,columns in additions.items():
            existing = {column['name'] for column in inspect(connection).get_columns(table)}
            for name,definition in columns.items():
                if name not in existing:
                    connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
                    if table == 'user' and name == 'demo_doctor':
                        connection.exec_driver_sql("UPDATE user SET demo_doctor=1 WHERE role='doctor' AND email='doctor@mediqueue.test'")
                    if table == 'doctor' and name == 'active':
                        connection.exec_driver_sql("UPDATE doctor SET active=0 WHERE name='Dr. Juan Reyes' AND department='General Medicine'")
