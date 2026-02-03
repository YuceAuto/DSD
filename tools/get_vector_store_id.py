from openai import OpenAI

client = OpenAI()

def get_or_create_vs_id(name="SkodaKB"):
    for vs in client.vector_stores.list(limit=100).data:
        if vs.name == name:
            return vs.id
    return client.vector_stores.create(name=name).id

if __name__ == "__main__":
    vs_id = get_or_create_vs_id("SkodaKB")
    print("VECTOR_STORE_ID =", vs_id)