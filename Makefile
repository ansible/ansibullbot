.PHONY: init tests
init:
	pip install -r requirements.txt

tests:
	PYTHONPATH=($pwd) python setup.py nosetests
