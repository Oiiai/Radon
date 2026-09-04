import rdn

with open("123.rdn", "r") as f:
    data = rdn.load(f)

print(data['fun']['6767'])