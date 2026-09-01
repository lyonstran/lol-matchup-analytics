from common import s3

test_key = "raw/_healthcheck.json"

print(f"Bucket: {s3.bucket()}")
s3.put_json(test_key, {"hello": "s3"})
print(f"Wrote {test_key}")
print(f"Exists check: {s3.object_exists(test_key)}")
print(f"Missing check: {s3.object_exists('raw/_does_not_exist.json')}")