import time

import httpx

BASE_URL = "http://127.0.0.1:8000"

TEST_DOCUMENT = {
    "filename": "eval_doc.txt",
    "content": (
        "FastAPI is a modern Python web framework. It is fast, easy to use, "
        "and has automatic interactive documentation. Postgres is a powerful "
        "open-source relational database. Redis is an in-memory data store "
        "often used for caching and rate limiting."
    ),
}

TEST_CASES = [
    {"question": "What is FastAPI?", "expected_keywords": ["python", "web framework"]},
    {"question": "What is Postgres?", "expected_keywords": ["relational database"]},
    {"question": "What is Redis used for?", "expected_keywords": ["caching"]},
    {"question": "What is the capital of France?", "expected_keywords": ["don't know", "not"]},
]


def main():
    # create a fresh tenant just for this eval run, so it never depends on
    # or pollutes any tenant you've been testing with manually
    tenant_resp = httpx.post(f"{BASE_URL}/tenants", json={"name": "eval-tenant"})
    api_key = tenant_resp.json()["api_key"]
    headers = {"X-API-Key": api_key}

    upload_resp = httpx.post(f"{BASE_URL}/documents", json=TEST_DOCUMENT, headers=headers)
    job_id = upload_resp.json()["job_id"]

    status = "pending"
    while status not in ("done", "failed"):
        time.sleep(1)
        status_resp = httpx.get(f"{BASE_URL}/jobs/{job_id}", headers=headers)
        status = status_resp.json()["status"]

    if status != "done":
        print("Setup failed: document did not process successfully")
        return

    passed = 0
    for case in TEST_CASES:
        query_resp = httpx.post(f"{BASE_URL}/query", json={"question": case["question"]}, headers=headers)
        answer = query_resp.json()["answer"].lower()

        hit = any(keyword.lower() in answer for keyword in case["expected_keywords"])
        result = "PASS" if hit else "FAIL"
        passed += hit

        print(f"[{result}] {case['question']}")
        print(f"    answer: {answer}")

    print(f"\n{passed}/{len(TEST_CASES)} test cases passed")


if __name__ == "__main__":
    main()
