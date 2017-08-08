.PHONY: init tests
init:
	pip install -r requirements.txt

tests:
	# epdb nose plugin breaks distutils somehow
	#PYTHONPATH=$(shell pwd) python setup.py nosetests
	PYTHONPATH=$(shell pwd) nosetests -v tests
