"""
Route module — all 118 REST endpoints for the Robotic Digital Twin.

Each router reads from MongoDB via motor async driver.
Graceful degradation: if MongoDB unavailable, return empty data with 200.
"""
