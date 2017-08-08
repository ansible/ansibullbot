.PHONY: init tests
init:
	pip install -r requirements.txt

tests:
	PYTHONPATH=$(shell pwd) python setup.py nosetests
