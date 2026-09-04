#!/bin/sh
sed -i "s|websearch_to_tsquery('simple',%s)|websearch_to_tsquery('simple',replace(%s, ' ', ' OR '))|g" /opt/maxkb-app/apps/knowledge/sql/keywords_search.sql
grep -n 'websearch_to_tsquery' /opt/maxkb-app/apps/knowledge/sql/keywords_search.sql
