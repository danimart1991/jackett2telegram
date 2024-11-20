# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r /app/requirements.txt

# Define environment variable
ENV TOKEN X
ENV CHATID X
ENV DELAY 600
ENV LOG_LEVEL INFO

# Run app.py when the container launches
CMD ["sh", "-c", "python jackett2telegram.py --token ${TOKEN} --chat_id ${CHATID} --delay ${DELAY} --log_level ${LOG_LEVEL}"]
