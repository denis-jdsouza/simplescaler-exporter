FROM python:3.6.12-alpine as base
LABEL maintainer="Denis DSouza"
FROM base as builder

COPY requirements.txt /requirements.txt
RUN pip install --user --no-warn-script-location -r requirements.txt

FROM base
COPY --from=builder /root/.local /root/.local

COPY src /app
WORKDIR /app
ENV PATH=/root/.local/bin:$PATH
EXPOSE 8000
CMD [ "python", "main.py" ]