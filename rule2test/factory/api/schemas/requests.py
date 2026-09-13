"""Small strict transport contracts; domain validation stays in the existing services."""
import base64,ntpath
from factory.models.common import require,nonempty

def body_keys(body,required,optional=()):
    require(type(body) is dict,"Expected a JSON object")
    require(set(required)<=set(body) and set(body)<=set(required)|set(optional),"Missing or unexpected request fields")
    return body

def actor(body):
    value=body["actor"];nonempty(value,"actor")
    require(len(value)<=100,"Actor name exceeds 100 characters")
    return value

def upload(body):
    name=body["filename"]
    require(type(name) is str and 0<len(name)<=160 and ntpath.basename(name)==name and not any(ord(c)<32 for c in name),"Invalid upload filename")
    require(type(body["content_base64"]) is str,"Expected base64 file data")
    try:data=base64.b64decode(body["content_base64"],validate=True)
    except ValueError as exc:raise ValueError("Invalid base64 upload") from exc
    require(0<len(data)<=10*1024*1024,"Upload must be 1 byte..10 MiB")
    return name,data
