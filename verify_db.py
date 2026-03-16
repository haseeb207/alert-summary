#!/usr/bin/env python3
import sqlite3
import os

db_path = 'alerts.db'

if not os.path.exists(db_path):
    print("❌ Database not found")
    exit(1)

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Count alerts
    cursor.execute("SELECT COUNT(*) FROM alerts")
    total = cursor.fetchone()[0]
    print(f"✅ Total alerts stored: {total}")
    
    if total > 0:
        # Show by operation/service
        cursor.execute("""
        SELECT operation, service, COUNT(*) as count, severity
        FROM alerts 
        GROUP BY operation, service, severity
        ORDER BY count DESC
        """)
        
        print("\n📊 Alerts by operation/service/severity:")
        for row in cursor.fetchall():
            print(f"  • {row[0]:30} | {row[1]:20} | {row[3]:8} | count={row[2]}")
        
        # Check aggregated periods
        cursor.execute("SELECT COUNT(*) FROM alert_periods")
        periods = cursor.fetchone()[0]
        print(f"\n🔔 Aggregated periods: {periods}")
        
        if periods > 0:
            cursor.execute("""
            SELECT period_start, operation, service, total_count, trend_direction
            FROM alert_periods
            ORDER BY period_start DESC
            LIMIT 5
            """)
            
            print("\n📈 Recent aggregated periods:")
            for row in cursor.fetchall():
                print(f"  • {row[0]} | {row[1]:30} | {row[2]:20} | count={row[3]} | trend={row[4]}")
    
    conn.close()
    print("\n✅ Database validation passed")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
