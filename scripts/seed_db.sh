#!/bin/bash
set -e
echo "🌱 Seeding demo database..."
PYTHONPATH=. python3 data/mock/seed.py
echo "✅ Database seeded successfully!"
