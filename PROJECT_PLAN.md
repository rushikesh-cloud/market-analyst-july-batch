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