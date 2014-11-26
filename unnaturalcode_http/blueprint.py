from flask import Blueprint, abort

unnaturalrest = Blueprint('unnatural-rest', __name__)

@unnaturalrest.route('/hello')
def test():
    return 'Hello, World!'
