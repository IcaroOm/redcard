run:
	poetry run python manage.py runserver 
migrate:
	poetry run python manage.py migrate 
test:
	pytest -x -vv
coverage:
	pytest --cov=. --cov-report xml --cov-report term:skip-covered --cov-report html
format:
	blue .
