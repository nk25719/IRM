Use this workflow:

## 1. Edit locally first

Work in your local folder:

```bash
cd ~/Downloads/biomed_inventory_app-3
```

Edit files:

* UI/design: `app/static/index.html`
* backend/API/database logic: `app/main.py`
* dependencies: `requirements.txt`

## 2. Build 

// check docker file 
cd /Users/naghamkheir/Repos/IRM/biomed_inventory_app
ls. 

// build 
docker build -t cmm-inventory . 


## 3. Test locally

```bash
docker build -t cmm-inventory .
docker run -p 8080:8080 cmm-inventory
```

Open:

```text
```

Test the change.

## 4. Deploy online

When it works locally:

```bash
gcloud run deploy cmm-inventory \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## 5. Verify live app

Open:

```text
https://cmm-inventory-979683804007.us-central1.run.app
```

## 6. Best practice

Before editing, make a backup:

```bash
cp app/main.py app/main_backup.py
cp app/static/index.html app/static/index_backup.html
```

