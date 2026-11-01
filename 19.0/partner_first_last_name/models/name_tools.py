"""Splitting and joining person names (no Odoo dependency, easy to test)."""

ORDERS = [
    ('first_last', 'First Last (John Smith)'),
    ('last_first', 'Last First (Smith John)'),
    ('last_comma_first', 'Last, First (Smith, John)'),
]

# words that belong to the last name: "Ludwig van Beethoven", "Maria de la Cruz"
PARTICLES = {'van', 'von', 'der', 'den', 'de', 'del', 'della', 'di', 'da', 'du', 'des', 'la', 'le', 'ter', 'ten',
             'bin', 'binti', 'al', 'el', 'dos', 'das', 'do', "d'", 'st.', 'saint', 'mac', 'vom', 'zu', 'y'}


def clean(value):
    return ' '.join((value or '').split())


def join_name(first, middle, last, order='first_last'):
    first, middle, last = clean(first), clean(middle), clean(last)
    given = ' '.join(p for p in (first, middle) if p)
    if order == 'last_first':
        return ' '.join(p for p in (last, given) if p)
    if order == 'last_comma_first':
        if last and given:
            return f'{last}, {given}'
        return last or given
    return ' '.join(p for p in (given, last) if p)


def split_name(name, order='first_last', use_middle=False):
    """Return (first, middle, last) for ``name`` written in ``order``."""
    name = clean(name)
    if not name:
        return '', '', ''
    if ',' in name:
        last, given = (clean(part) for part in name.split(',', 1))
        tokens = given.split()
        if not tokens:
            return '', '', last
        if use_middle:
            return tokens[0], ' '.join(tokens[1:]), last
        return ' '.join(tokens), '', last
    tokens = name.split()
    if len(tokens) == 1:
        return tokens[0], '', ''
    if order in ('last_first', 'last_comma_first'):
        end = 1
        while end < len(tokens) - 1 and tokens[end - 1].lower() in PARTICLES:
            end += 1
        last, given = tokens[:end], tokens[end:]
        if use_middle:
            return given[0], ' '.join(given[1:]), ' '.join(last)
        return ' '.join(given), '', ' '.join(last)
    start = len(tokens) - 1
    while start > 1 and tokens[start - 1].lower() in PARTICLES:
        start -= 1
    given, last = tokens[:start], tokens[start:]
    if use_middle:
        return given[0], ' '.join(given[1:]), ' '.join(last)
    return ' '.join(given), '', ' '.join(last)
