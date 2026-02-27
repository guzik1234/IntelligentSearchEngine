# IntelligentSearchEngine
This search engine is supposed to show operations on a specific database of videos, such as viewing times, in which categories, in a word, artificial intelligence is supposed to work here

# Movie Insights Agent

## Problem biznesowy
Analitycy i PM potrzebują szybkich odpowiedzi z danych platformy filmowej bez ręcznego pisania SQL.

## Cel projektu
Użytkownik zadaje pytanie po polsku, system zwraca:
- SQL
- tabelę wyników
- wykres
- krótki insight

## Zakres MVP
- NL -> SQL (pytania analityczne)
- Walidacja bezpieczeństwa (`SELECT only`)
- Wizualizacja wyników

## Metryki sukcesu
- % poprawnych zapytań SQL
- median latency
- % poprawnych odpowiedzi merytorycznych

## Poza zakresem
- streaming video
- płatności
- rozbudowany system kont
