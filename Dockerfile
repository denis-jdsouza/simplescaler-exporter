FROM python:3.6
LABEL maintainer="Denis DSouza"
WORKDIR /app
COPY src .
COPY requirements.txt .
RUN pip install -r requirements.txt
EXPOSE 8000
CMD [ "python", "main.py" ]