# TeamOrbit

Online Software Project Management Tool.

## Vercel deployment

This repository is configured for Vercel with the Flask app exposed through `api/index.py` and a rewrite that sends all application routes to Flask.

### Local run

```text
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`

### Demo admin

```text
Email: admin@teamorbit.com
Password: admin123
```

## Important database note

The Vercel configuration uses temporary `/tmp/teamorbit.db` storage so the application can execute in the serverless environment. This is suitable for a demonstration/runtime check but is not persistent across serverless instances. For permanent online data, connect the application to a hosted database later.
