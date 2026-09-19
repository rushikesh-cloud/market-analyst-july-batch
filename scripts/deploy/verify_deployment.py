"""Check HTTPS, frontend assets, protected routes, and every ACI container."""
import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.paths.append(attrs['src'])


def verify(url):
    with urllib.request.urlopen(url + '/api/health', timeout=15) as response:
        assert json.load(response) == {'status': 'healthy'}
    with urllib.request.urlopen(url, timeout=15) as response:
        html = response.read().decode()
        assert 'id="root"' in html
    parser = Assets()
    parser.feed(html)
    assert parser.paths, 'Frontend script missing'
    for path in parser.paths:
        with urllib.request.urlopen(urljoin(url, path), timeout=15) as response:
            assert 'javascript' in response.headers['Content-Type']
    try:
        urllib.request.urlopen(url + '/api/auth/me', timeout=15)
    except urllib.error.HTTPError as error:
        assert error.code == 401, f'Expected authentication challenge, got {error.code}'
    else:
        raise AssertionError('Protected endpoint accepted anonymous access')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resource-group', required=True)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    for attempt in range(40):
        state = json.loads(subprocess.check_output([
            'az', 'container', 'show', '-g', args.resource_group, '-n', args.name,
            '--query', '{fqdn:ipAddress.fqdn,containers:containers[].{name:name,state:instanceView.currentState.state}}', '-o', 'json'], text=True))
        try:
            assert state['fqdn'], 'Waiting for DNS'
            assert all(item['state'] == 'Running' for item in state['containers']), 'Waiting for containers'
            verify('https://' + state['fqdn'])
        except (AssertionError, OSError, ValueError) as error:
            print(f'Attempt {attempt + 1}: {type(error).__name__}; waiting for HTTPS readiness.', flush=True)
            time.sleep(15)
        else:
            print(f"Verified https://{state['fqdn']} (health, frontend assets, authentication, all containers).")
            return
    raise SystemExit('Deployment did not pass readiness checks within 10 minutes.')


if __name__ == '__main__':
    main()
