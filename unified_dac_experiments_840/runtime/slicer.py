"""Deterministic, conservative statement-level Python/HCL backward slicer.

Supports .next =, .eq(), @=, <<=, |=, indexed writes, Python guards,
with m.If/Switch/Case, Migen If/Case, decorators, loop guards and helpers.
No candidate execution. Aliasing/dynamic Python remain conservative.
"""
import ast

def symbol(n):
    if isinstance(n, ast.Name): return n.id
    if isinstance(n, ast.Attribute):
        if n.attr == 'next': return symbol(n.value)
        p = symbol(n.value)
        return p + '.' + n.attr if p else None
    if isinstance(n, ast.Subscript): return symbol(n.value)
    return None

def refs(n):
    result = set()
    def visit(x):
        if isinstance(x, ast.Attribute):
            s = symbol(x)
            if s: result.add(s)
            else: visit(x.value)
        elif isinstance(x, ast.Name): result.add(x.id)
        else:
            for c in ast.iter_child_nodes(x): visit(c)
    if n is not None: visit(n)
    return result

def targets(n):
    if isinstance(n, (ast.Tuple, ast.List)):
        return set().union(*(targets(e) for e in n.elts))
    s = symbol(n)
    return {s} if s else set()

def target_indices(n):
    return set().union(*(refs(x.slice) for x in ast.walk(n) if isinstance(x,ast.Subscript)))

def slice_source(code, output, seed_lines=(), output_names=None):
    tree = ast.parse(code); lines = code.splitlines(); records = []; helpers = {}
    def span(n): return set(range(n.lineno, n.end_lineno + 1))
    def header(n):
        body = getattr(n, 'body', [])
        end = body[0].lineno - 1 if body else n.lineno
        result = set(range(n.lineno, max(n.lineno, end) + 1))
        for d in getattr(n, 'decorator_list', []): result |= span(d)
        return result
    def add(dst, dep, n, ctxlines, ctxdeps):
        if dst: records.append({'targets': dst, 'deps': dep | ctxdeps,
                                 'lines': span(n) | ctxlines, 'anchor': n.lineno})
    def block(body, ctxlines, ctxdeps):
        prior_guard=set();prior_headers=set()
        for child in body:
            extra=set();headers=set()
            if isinstance(child,ast.With) and child.items:
                expression=child.items[0].context_expr
                name=expression.func.attr if isinstance(expression,ast.Call) and isinstance(expression.func,ast.Attribute) else ''
                if name=='If':prior_guard=refs(expression);prior_headers=header(child)
                elif name in {'Elif','Else'}:
                    extra=prior_guard.copy();headers=prior_headers.copy()
                    prior_guard |= refs(expression);prior_headers |= header(child)
                else:prior_guard=set();prior_headers=set()
            else:prior_guard=set();prior_headers=set()
            visit(child,ctxlines|headers,ctxdeps|extra)
    def visit(n, ctxlines=set(), ctxdeps=set()):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                helpers[n.name] = n
            block(n.body, ctxlines | header(n), ctxdeps)
            return
        if isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.AsyncWith)):
            guard = refs(n.test) if isinstance(n, (ast.If, ast.While)) else refs(n.iter) if isinstance(n, ast.For) else set().union(*(refs(i.context_expr) for i in n.items))
            h = header(n)
            block(n.body, ctxlines | h, ctxdeps | guard)
            for c in getattr(n, 'orelse', []):
                # Include else/elif label without pulling in the sibling body.
                label = c.lineno - 1
                for j in range(c.lineno - 1, n.lineno, -1):
                    if lines[j-1].lstrip().startswith(('else:', 'elif ')):
                        label = j; break
                visit(c, ctxlines | h | {label}, ctxdeps | guard)
            return
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            value = n.value
            eqs = [x for x in ast.walk(value) if isinstance(x, ast.Call)
                   and isinstance(x.func, ast.Attribute) and x.func.attr == 'eq'] if value else []
            if eqs:
                # Each equation is a separate dependency, even in a comb list.
                for x in eqs:
                    dep = set().union(*(refs(a) for a in x.args)) | target_indices(x.func.value)
                    control_lines = {n.lineno}
                    # Hardware If/Case calls enclosing eq carry control deps.
                    for p in ast.walk(value):
                        if isinstance(p, ast.Call) and x in list(ast.walk(p)) and p is not x:
                            callname = p.func.id if isinstance(p.func, ast.Name) else p.func.attr if isinstance(p.func, ast.Attribute) else ''
                            if callname in {'If','Elif','Else','Case'}:
                                control_lines |= {p.lineno, p.func.end_lineno}
                            if callname in {'If', 'Elif', 'Case'} and p.args:
                                dep |= refs(p.args[0])
                            # Else/Elif chains keep the original If condition in func.value.
                            for q in ast.walk(p.func):
                                if isinstance(q, ast.Call):
                                    qname=q.func.id if isinstance(q.func,ast.Name) else q.func.attr if isinstance(q.func,ast.Attribute) else ''
                                    if qname in {'If','Elif','Case'} and q.args: dep |= refs(q.args[0])
                    add(targets(x.func.value), dep, x, ctxlines | control_lines, ctxdeps)
            else:
                ts = set().union(*(targets(t) for t in n.targets)) if isinstance(n, ast.Assign) else targets(n.target)
                lhs=n.targets if isinstance(n,ast.Assign) else [n.target]
                add(ts, refs(value)|set().union(*(target_indices(t) for t in lhs)), n, ctxlines, ctxdeps)
            return
        if isinstance(n, ast.Expr):
            for x in ast.walk(n):
                if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == 'eq':
                    add(targets(x.func.value), set().union(*(refs(a) for a in x.args)), n, ctxlines, ctxdeps)
        for c in ast.iter_child_nodes(n): visit(c, ctxlines, ctxdeps)
    visit(tree)
    need = {output, 's.' + output, 'self.' + output}; selected = set(); chosen = set()
    # PyRTL may return a literal/expression or an alias whose Python name differs
    # from the public output. Bind return position using the public interface.
    if output_names and output in output_names:
        top=next((n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='TopModule'),None)
        def bind_returns(n):
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and n is not top:return
            if isinstance(n,ast.Return) and n.value is not None:
                value=n.value
                if isinstance(value,(ast.Tuple,ast.List)) and len(value.elts)==len(output_names):value=value.elts[output_names.index(output)]
                virtual='__observed_return__.'+output
                records.append({'targets':{virtual},'deps':refs(value),'lines':span(value)|header(top)|{n.lineno},'anchor':n.lineno})
                need.add(virtual)
            for c in ast.iter_child_nodes(n):bind_returns(c)
        if top:bind_returns(top)
    seeds = set(seed_lines)
    while True:
        before = (len(need), len(chosen))
        for i, r in enumerate(records):
            if i in chosen: continue
            if r['targets'] & need or (r['lines'] & seeds and r['anchor'] in seeds):
                chosen.add(i); selected |= r['lines']; need |= r['deps']
        for name in need.copy():
            if name in helpers and name not in {'TopModule', 'construct', '__init__', 'elaborate'}:
                h = helpers[name]
                # Include called helper body, and backtrack its external reads.
                selected |= span(h); need |= refs(h)
        if before == (len(need), len(chosen)): break
    selected = sorted(i for i in selected if 1 <= i <= len(lines))
    return {'method': 'python_ast_static_backward_slice', 'failing_output': output,
            'nonempty': bool(chosen), 'statement_count': len(chosen), 'source_line_numbers': selected,
            'dependencies': sorted(need),
            'source': '\n'.join(f'L{i}: {lines[i-1]}' for i in selected),
            'scope': 'conservative static dependencies, control contexts and called helper bodies; no path feasibility claim'}

def trace_text(code, output, runtime=None, output_names=None):
    anchors = {b['line'] for n in (runtime or {}).get('nets', []) for b in n['source_bindings']}
    result = slice_source(code, output, anchors, output_names)
    if runtime:
        result.update(method='pyrtl_runtime_cone_plus_ast', block_net_count=runtime['block_net_count'],
                      cone_net_count=runtime['net_count'])
        result['netlist_included'] = runtime['block_net_count'] <= 40
        if result['netlist_included']: result['nets'] = runtime['nets']
    return result
