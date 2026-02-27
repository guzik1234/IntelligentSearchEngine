# IntelligentSearchEngine
This search engine is supposed to show operations on a specific database of videos, such as viewing times, in which categories, in a word, artificial intelligence is supposed to work here

# Movie Insights Agent

## Business Problem
Analysts and PMs need quick answers from movie-platform data without manually writing SQL.

## Project Goal
The user asks a question in natural language, and the system returns:
- SQL query
- result table
- chart
- short insight

## MVP Scope
- NL -> SQL (analytical questions)
- safety validation (`SELECT only`)
- result visualization

## Success Metrics
- % of correct SQL queries
- median latency
- % of factually correct answers

## Out of Scope
- video streaming
- payments
- advanced account system
