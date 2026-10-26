import boto3, gzip, re, sys, collections

bucket = sys.argv[1]
s3 = boto3.client("s3")
groups = collections.OrderedDict()
pat = re.compile(r"/(dt|hr|hour|year|month|day|partition)=[^/]*")
n = 0
for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
    for o in page.get("Contents", []):
        n += 1
        k = o["Key"]
        folder = pat.sub("/*", k.rsplit("/", 1)[0]) if "/" in k else "(root)"
        g = groups.setdefault(folder, {"n": 0, "bytes": 0, "sample": k, "first": o["LastModified"], "last": o["LastModified"]})
        g["n"] += 1
        g["bytes"] += o["Size"]
        g["first"] = min(g["first"], o["LastModified"])
        g["last"] = max(g["last"], o["LastModified"])

print(f"TOTAL OBJECTS: {n}\n")
for f, g in groups.items():
    print(f"{f}\n  files={g['n']} size={g['bytes']/1e6:.1f}MB  {g['first']:%Y-%m-%d %H:%M} -> {g['last']:%Y-%m-%d %H:%M}\n  sample={g['sample']}")

print("\n==== SAMPLE CONTENT ====")
for f, g in groups.items():
    k = g["sample"]
    body = s3.get_object(Bucket=bucket, Key=k, Range="bytes=0-200000")["Body"].read()
    try:
        if k.endswith(".gz"):
            body = gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body
    except Exception:
        d = __import__("zlib").decompressobj(31)
        body = d.decompress(body)
    text = body.decode("utf-8", "replace").splitlines()
    print(f"\n--- {k}")
    for line in text[:3]:
        print("  " + line[:600])
