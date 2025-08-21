# Use an official Python runtime as a parent image
FROM python:3.13-alpine

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --trusted-host pypi.python.org -r /app/requirements.txt

# Define environment variable
ENV TOKEN=X
ENV CHATID=X
ENV MESSAGE_THREAD_ID=""
ENV DELAY=600
ENV LOG_LEVEL=INFO

# Make entrypoint script executable
RUN chmod +x /app/docker-entrypoint.sh

# Run entrypoint script when container launches
CMD ["/app/docker-entrypoint.sh"]
