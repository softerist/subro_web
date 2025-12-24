#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Ensure we can change to the directory
target_dir="/home/user/subro_web/infra/docker"
if [ ! -d "$target_dir" ]; then
    echo "❌ Error: Directory $target_dir not found."
    exit 1
fi
cd "$target_dir"

echo "🧹 Cleaning up existing containers..."
docker-compose down --remove-orphans -v
# Clean up specific containers if they exist
docker ps -aq --filter "name=docker_" --filter "name=subapp" | xargs -r docker rm -f

echo "🔍 Checking for port conflicts..."
# Check if ports 6379, 5432, 8080, 5173, or 8000 are in use
PORTS_IN_USE=$(sudo netstat -tlnp | grep -E ':(6379|5432|8080|5173|8000)' | wc -l)

if [ "$PORTS_IN_USE" -gt 0 ]; then
    echo "⚠️  Warning: Some ports are still in use:"
    sudo netstat -tlnp | grep -E ':(6379|5432|8080|5173|8000)'
    echo ""
    echo "Would you like to stop local services? (y/n)"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        sudo systemctl stop redis-server 2>/dev/null || echo "Redis not running as service"
        sudo systemctl stop postgresql 2>/dev/null || echo "PostgreSQL not running as service"
    fi
fi

echo "🚀 Starting containers..."
docker-compose up -d --build

echo "⏳ Waiting for services to be healthy (30 seconds)..."
sleep 30

echo "📊 Container status:"
docker-compose ps

echo ""
echo "🔍 Verifying /tmp mount in API container..."
if docker-compose exec -T api ls -la /tmp > /dev/null 2>&1; then
    echo "✅ /tmp is accessible"
    if docker-compose exec -T api touch /tmp/test_write 2>/dev/null; then
        echo "✅ /tmp is writable"
        docker-compose exec -T api rm /tmp/test_write
    else
        echo "❌ /tmp is not writable"
    fi
else
    echo "❌ Cannot access /tmp in container"
fi

echo ""
echo "⚙️  Checking ALLOWED_FOLDERS setting..."
docker-compose exec -T api env | grep ALLOWED_FOLDERS || echo "⚠️  ALLOWED_FOLDERS not set"

echo ""
echo "✅ Setup complete! Now run your tests:"
echo "   cd /home/user/subro_web/backend"
echo "   pytest tests/integration/test_job_log_streaming.py -v -s"
