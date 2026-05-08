"""
Candidate bank business logic service.
Boolean search query parsing and search field configuration.
"""
import re
from typing import List


# Fields used for boolean text search across candidate records
SEARCH_FIELDS = [
    "name", "email", "phone", "key_skills", "skills",
    "current_designation", "designation", "headline",
    "current_company", "company", "location", "current_location",
]


def _term_to_mongo(term: str) -> dict:
    """Convert a single search term to a MongoDB $or across all searchable fields."""
    pattern = re.escape(term)
    return {"$or": [{f: {"$regex": pattern, "$options": "i"}} for f in SEARCH_FIELDS]}


def parse_boolean_query(query: str) -> dict:
    """
    Parse a boolean search string into a MongoDB filter.
    Supports:
      - Quoted phrases: "machine learning"
      - AND (explicit or implicit space-separated)
      - OR
      - NOT / -term
      - Parentheses for grouping
    """
    if not query or not query.strip():
        return {}

    tokens = []
    i = 0
    q = query.strip()

    while i < len(q):
        if q[i] in '()':
            tokens.append(q[i])
            i += 1
        elif q[i] == '"':
            end = q.find('"', i + 1)
            if end == -1:
                end = len(q)
            tokens.append(('TERM', q[i + 1:end]))
            i = end + 1
        elif q[i].isspace():
            i += 1
        else:
            j = i
            while j < len(q) and not q[j].isspace() and q[j] not in '()"':
                j += 1
            word = q[i:j]
            upper = word.upper()
            if upper == 'AND':
                tokens.append('AND')
            elif upper == 'OR':
                tokens.append('OR')
            elif upper == 'NOT':
                tokens.append('NOT')
            elif word.startswith('-') and len(word) > 1:
                tokens.append('NOT')
                tokens.append(('TERM', word[1:]))
            else:
                tokens.append(('TERM', word))
            i = j

    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def parse_expr():
        left = parse_or()
        return left

    def parse_or():
        left = parse_and()
        while peek() == 'OR':
            consume()
            right = parse_and()
            left_ors = left.get('$or', [left]) if '$or' in left else [left]
            right_ors = right.get('$or', [right]) if '$or' in right else [right]
            left = {"$or": left_ors + right_ors}
        return left

    def parse_and():
        left = parse_not()
        while pos[0] < len(tokens):
            p = peek()
            if p == 'AND':
                consume()
                right = parse_not()
            elif isinstance(p, tuple) or p == 'NOT' or p == '(':
                right = parse_not()
            else:
                break
            left_ands = left.get('$and', [left]) if '$and' in left else [left]
            right_ands = right.get('$and', [right]) if '$and' in right else [right]
            left = {"$and": left_ands + right_ands}
        return left

    def parse_not():
        if peek() == 'NOT':
            consume()
            operand = parse_primary()
            return {"$nor": [operand]}
        return parse_primary()

    def parse_primary():
        p = peek()
        if p == '(':
            consume()
            expr = parse_expr()
            if peek() == ')':
                consume()
            return expr
        elif isinstance(p, tuple) and p[0] == 'TERM':
            consume()
            return _term_to_mongo(p[1])
        else:
            if pos[0] < len(tokens):
                consume()
            return {}

    if not tokens:
        return {}

    try:
        result = parse_expr()
        return result if result else {}
    except (IndexError, RecursionError):
        terms = re.findall(r'"([^"]+)"|(\S+)', query)
        flat = [t[0] or t[1] for t in terms if t[0] or t[1]]
        if flat:
            return {"$and": [_term_to_mongo(t) for t in flat if t.upper() not in ('AND', 'OR', 'NOT')]}
        return {}
