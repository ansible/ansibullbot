init:
	pip install -r requirements.txt

tests:
	PYTHONPATH=($pwd) nosetests -v --logging-level=DEBUG --nocapture `find test -name "test_*.py"`
