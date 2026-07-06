FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY fifa_index.html build_data.py ./
CMD ["python", "build_data.py", "fifa_index.html"]
