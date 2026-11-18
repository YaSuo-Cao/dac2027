"""Portable transport adapter. Credentials are supplied only by environment."""
import json
import os
import urllib.error
import urllib.request


def credential():
    value = os.environ.get('OPENCODE_API_KEY')
    if not value:
        raise RuntimeError('Set OPENCODE_API_KEY in your environment before a new model run')
    return value


def transport(payload, key, session):
    claude = payload.get('model', '').startswith('claude-')
    base = os.environ.get('PARAROUTE_API_BASE', 'https://opencode.ai/zen/go/v1').rstrip('/')
    headers = {'Content-Type': 'application/json', 'x-opencode-session': session}
    if claude:
        headers.update({'x-api-key': key, 'anthropic-version': '2023-06-01'})
        body = {'model': payload['model'], 'max_tokens': payload.get('max_tokens', 4096),
                'messages': [m for m in payload['messages'] if m['role'] != 'system']}
        system = [m['content'] for m in payload['messages'] if m['role'] == 'system']
        if system:
            body['system'] = '\n\n'.join(system)
        # The evaluated Messages endpoint rejects these sampling controls.
        url = base + '/messages'
    else:
        headers['Authorization'] = 'Bearer ' + key
        body = payload
        url = base + '/chat/completions'
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            status, text = response.status, response.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as error:
        return {'status': error.code, 'body': error.read().decode('utf-8', errors='replace').replace(key, '[REDACTED]')}
    except Exception as error:
        return {'status': 0, 'body': str(error).replace(key, '[REDACTED]')}
    if status == 200 and claude:
        raw = json.loads(text)
        usage = raw.get('usage') or {}
        normalized_usage = {'prompt_tokens': usage.get('input_tokens', 0),
                            'completion_tokens': usage.get('output_tokens', 0),
                            'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0)}
        if 'cache_read_input_tokens' in usage:
            normalized_usage['prompt_tokens_details'] = {'cached_tokens': usage['cache_read_input_tokens']}
        text = json.dumps({'id': raw.get('id'), 'model': raw.get('model', payload['model']),
                           'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': ''.join(
                               b.get('text', '') for b in raw.get('content', []) if b.get('type') == 'text')},
                               'finish_reason': 'length' if raw.get('stop_reason') == 'max_tokens' else 'stop'}],
                           'usage': normalized_usage, 'provider_protocol': 'anthropic_messages',
                           'anthropic_stop_reason': raw.get('stop_reason')})
    return {'status': status, 'body': text}
