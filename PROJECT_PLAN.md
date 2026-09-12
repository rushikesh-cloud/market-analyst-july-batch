Functional Requirements

Stock Market Analysis Platform

- Good Performing Stocks in the Market
- Stocks
  - Financials (Agent with access to PDF reports (chunked to the vector db), agent will gather all the financials )
  - Technical (multi modal, text, different agent, who will have yahoo finance access to get the prices and charting tool access to generate the charts )
  - News (Stock related news, Global News, Sector Related News, Peer, Agent with access to Tavily to search the web and gather recent news around the differnet factors mentioned)
  - Every agent will provide Ratings, plus reasoning
  - One supervisor agent to manage the above agents and do a thorought stock analysis and provide again rating and reasoning
    Dashboard
    AI Chat Agent

Technical Requirements
----------------------

Postgres DB - Relational plus vector db plus chat sessions
AzureOpenAI models (gpt-terra, gpt-luna) (SDLC Automation, Agents)
Azure Document Intelligence
Containers to host the application (ACI)
GitHub / Actions
Evals / Guardrails / Observability
React / FastAPI

Azure (use az cli)

Resource Group - market-analyst-july-batch

AI Foudry - deploy luna, terra, embedding-large
Postgres - vectors enabled, full text based column (for rag based use case with hybrid search)
Azure dcoument intelligence
ACI

Github (use gh cli)

create new repo

UI / UX

Companies - where we can define the list of companies, Company Name, ticker, (ticker for yahoo finance)

- add companies
- table to show the list of companies configured,
- edit and delete option at a table level

Documents

- Documents at a compnay level and also years specified these would be a annual reports of a company
- user can upload a new document by selecting compnay name and year for the same
- this would trigger a ingestion inside the vector db
- - azure document intelligence parsing with output of markdown
- - chunking at a header level, tables chunked separately, overlap with each previous chunk of 50 tokens including tables chunks, at additinoal metadata would be type of chunk (table, para), header sequence
- When user opens a document we should be able to see the the pipeline and status of the same, fronend should poll the database for status, multiple tables, one tab for status, one tab with split screen of makrdown at left and chunks visible in right

Stock Analysis Interface

- start a new job by selecting the company from the dropdown and it will trigger the supervisor agent
- list of jobs run
- job will be running the supervisor agent, and would show the results for finance, technical and news agents also show the ratings

AI Chat Agent
Right side screen with collapsible chatbot where users can ask questions

Authentication
Signup / Signin


Merge chunks where smaller once can be combined to a total250 chunks