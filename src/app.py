from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from botocore.exceptions import (
    NoCredentialsError,
    PartialCredentialsError,
    EndpointConnectionError,
)
import boto3, os, dns.resolver
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="notes-fastapi")


region = os.getenv("AWS_REGION", "us-east-1")
ses_client = boto3.client("ses", region_name=region)


class EmailRequest(BaseModel):
    receiver_email: EmailStr
    subject: str
    body_text: str



def validate_email_domain(email: str):
    """Check if the email's domain has MX records (can receive mail)."""
    domain = email.split("@")[-1]
    try:
        dns.resolver.resolve(domain, "MX")
        return True
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=f"Domain '{domain}' has no MX records or cannot receive email",
        )


@app.post("/send-email")
def send_email(req: EmailRequest):
    source_email = os.getenv("SOURCE_EMAIL")

    if not source_email:
        raise HTTPException(status_code=500, detail="Source email not configured in environment")

    if not req.subject.strip() or not req.body_text.strip():
        raise HTTPException(status_code=400, detail="Subject and body cannot be empty")

    validate_email_domain(req.receiver_email)

    try:
        ses_client.send_email(
            Source=source_email,
            Destination={"ToAddresses": [req.receiver_email]},
            Message={
                "Subject": {"Data": req.subject},
                "Body": {"Text": {"Data": req.body_text}},
            },
        )
        return {"message": f"Email successfully sent to {req.receiver_email}"}

   
    except ses_client.exceptions.MessageRejected:
        raise HTTPException(
            status_code=400,
            detail="Email rejected by AWS SES (unverified sender/recipient or invalid content)",
        )

    except ses_client.exceptions.ThrottlingException:
        raise HTTPException(
            status_code=429,
            detail="AWS SES rate limit exceeded. Please try again later.",
        )

  
    except NoCredentialsError:
        raise HTTPException(status_code=401, detail="AWS credentials not found")

    except PartialCredentialsError:
        raise HTTPException(status_code=401, detail="Incomplete AWS credentials")

    except EndpointConnectionError:
        raise HTTPException(
            status_code=503, detail="Unable to reach AWS SES endpoint (check region or network)"
        )

    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")



@app.get("/test-aws")
def test_aws():
    """Simple test to check if AWS SES endpoint is reachable."""
    import requests

    try:
        url = f"https://email.{region}.amazonaws.com"
        r = requests.get(url, timeout=5)
        return {"status": r.status_code, "text": r.text[:100]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Network test failed: {str(e)}")

