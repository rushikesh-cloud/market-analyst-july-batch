CREATE TABLE IF NOT EXISTS companies (
  id varchar(36) PRIMARY KEY,
  name varchar(200) NOT NULL,
  ticker varchar(40) NOT NULL UNIQUE
);
