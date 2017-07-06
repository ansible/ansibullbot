init:
	pip install -r requirements.txt

tests:
	PYTHONPATH=($pwd) nosetests -v --nocapture $@
