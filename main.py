from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "repo-qa-service is running"}
