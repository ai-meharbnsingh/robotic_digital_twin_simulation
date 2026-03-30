"""
Route module — all 64 API endpoints for the Robotic Digital Twin.

Each router reads from MongoDB via motor async driver.
Graceful degradation: if MongoDB unavailable, return empty data with 200.
"""
