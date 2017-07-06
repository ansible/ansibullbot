init:
	pip install -r requirements.txt

tests:
	PYTHONPATH=($pwd) nosetests -v --nocapture `find test -name "test_*.py"`
