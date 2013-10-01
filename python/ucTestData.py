somePythonCode = "print (1+2**2)"

someLexemes = [{'end': (1, 5), 'start': (1, 0), 'type': 'NAME', 'value': 'print'},
                {'end': (1, 8), 'start': (1, 7), 'type': 'OP', 'value': '('},
                {'end': (1, 9), 'start': (1, 8), 'type': 'NUMBER', 'value': '1'},
                {'end': (1, 10), 'start': (1, 9), 'type': 'OP', 'value': '+'},
                {'end': (1, 11), 'start': (1, 10), 'type': 'NUMBER', 'value': '2'},
                {'end': (1, 13), 'start': (1, 11), 'type': 'OP', 'value': '**'},
                {'end': (1, 14), 'start': (1, 13), 'type': 'NUMBER', 'value': '2'},
                {'end': (1, 15), 'start': (1, 14), 'type': 'OP', 'value': ')'},
                {'end': (2, 0), 'start': (2, 0), 'type': 'ENDMARKER', 'value': ''}]

indentLexeme =  {'end': (3, 8), 'start': (3, 0), 'type': 'INDENT', 'value': '        '}

lotsOfPythonCode = """
def mult(x, y):
    r = 0
    for _ in range(0, x):
        r = r + y

print mul(1, 2)
"""

