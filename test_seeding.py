from app import app

with app.test_client() as client:
    # Seed the tenant
    response = client.post("/api/tenants/059b6b17/seed",
        json={
            "num_customers": 5,
            "num_opportunities": 20
        },
        content_type="application/json")
    print(f"[OK] Seed response: {response.status_code}")
    print(f"  Message: {response.get_json().get('message')}")

    # Get tenant details with stats
    response = client.get("/api/tenants/059b6b17")
    print(f"[OK] Tenant details: {response.status_code}")
    data = response.get_json()
    print(f"  Customers: {data.get('customer_count')}")
    print(f"  Opportunities: {data.get('opportunity_count')}")
    print(f"  Total Value: ${data.get('total_opportunity_value'):,.0f}")

    # Get admin stats
    response = client.get("/api/admin/stats")
    print(f"[OK] Admin stats: {response.status_code}")
    stats = response.get_json()
    print(f"  Total Tenants: {stats.get('total_tenants')}")
    print(f"  Total Customers: {stats.get('total_customers')}")
    print(f"  Total Opportunities: {stats.get('total_opportunities')}")
