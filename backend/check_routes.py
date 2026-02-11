
from server import app

print('Routes defined in Flask app:')
for rule in app.url_map.iter_rules():
    print(f'{rule.endpoint:50s} {rule.methods} {rule}')
