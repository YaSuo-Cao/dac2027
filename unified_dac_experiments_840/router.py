"""Equation 4. No task identifier, category, reference, or native outcome input."""
import re

# Frozen before any new response. A clock and explicit arithmetic/pipeline prose
# are required for the hybrid branch; ambiguous prose uses the FC branch.
PATTERNS = {
    'pipeline': r'\b(?:pipeline[ds]?|pipelining|\d+[- ]stage|latency of \d+)\b',
    'arithmetic': r'\b(?:adder|addition|add(?:s|ing)?|subtract(?:or|ion|s)?|multipl(?:ier|y|ies|ication)|accumulat(?:or|e|es|ion)|arithmetic|sum|product)\b',
}

def route(public_ports, specification, gate_passed=True):
    if not gate_passed:
        return {'branch':'FL','has_clk':None,'matched_keywords':[], 'uses_task_identifier':False,'uses_category':False}
    has_clk=any((p.get('name') if isinstance(p,dict) else p[0])=='clk'
                and (p.get('direction','input') if isinstance(p,dict) else p[1]).lower().startswith('input')
                for p in public_ports)
    hits=sorted({m.group(0).lower() for pattern in PATTERNS.values()
                 for m in re.finditer(pattern,specification,re.I)})
    return {'branch':'FTL' if not has_clk else 'FCTL' if hits else 'FCL',
            'has_clk':has_clk, 'matched_keywords':hits if has_clk else [],
            'uses_task_identifier':False, 'uses_category':False}
