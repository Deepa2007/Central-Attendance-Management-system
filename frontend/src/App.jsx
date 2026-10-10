
import React, { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000';

function App() {
  const [token, setToken] = useState(localStorage.getItem('token') || '');
  const [user, setUser] = useState(JSON.parse(localStorage.getItem('user') || 'null'));
  const [today, setToday] = useState(null);
  const [compliance, setCompliance] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [deptFilter, setDeptFilter] = useState('');
  const [search, setSearch] = useState('');
  const [manualEntry, setManualEntry] = useState('2026-10-09T18:26:00');
  const [manualExit, setManualExit] = useState('2026-10-09T22:26:00');

  const headers = { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };

  const login = async (e) => {
    e.preventDefault();
    const email = e.target.email.value;
    const password = e.target.password.value;
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({email,password}) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login failed');
      setToken(data.access_token); setUser(data.user);
      localStorage.setItem('token', data.access_token); localStorage.setItem('user', JSON.stringify(data.user));
      fetchToday(data.access_token); fetchCompliance(data.access_token);
    } catch (err) { setMsg(err.message); }
  };

  const fetchToday = async (tok = token) => {
    if (!tok) return;
    try {
      const res = await fetch(`${API_BASE}/api/attendance/today`, { headers: { Authorization: `Bearer ${tok}` } });
      const data = await res.json();
      setToday(data);
    } catch {}
  };
  const fetchCompliance = async (tok = token, dept='') => {
    if (!tok) return;
    try {
      const body = dept ? { type:'compliance', department:dept } : { type:'compliance' };
      const res = await fetch(`${API_BASE}/api/attendance/reports`, { method:'POST', headers: { Authorization:`Bearer ${tok}`, 'Content-Type':'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      setCompliance(data.compliance || []);
    } catch {}
  };

  const markAttendance = async (payload = {}) => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/attendance/mark`, { method:'POST', headers, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) throw new Error(JSON.stringify(data));
      setMsg(`Marked: ${data.hours_worked} hrs, present=${data.is_present}, verified=${data.location?.verified}`);
      fetchToday(); fetchCompliance();
    } catch (e) { setMsg('Error: '+e.message); }
    setLoading(false);
  };

  const markWithLocation = () => {
    navigator.geolocation.getCurrentPosition(pos => {
      markAttendance({ lat: pos.coords.latitude, lng: pos.coords.longitude });
    }, () => markAttendance({ lat:17.3850, lng:78.4867 }));
  };

  useEffect(()=>{ if(token){ fetchToday(); fetchCompliance(); } }, [token]);

  if (!token) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-md">
          <h1 className="text-2xl font-bold text-white mb-2">Central Attendance</h1>
          <p className="text-slate-400 text-sm mb-6">Enterprise - 3 days / 15 hrs policy</p>
          <form onSubmit={login} className="space-y-4">
            <input name="email" defaultValue="admin@example.com" placeholder="Email" className="w-full bg-slate-800 text-white p-3 rounded-lg border border-slate-700"/>
            <input name="password" type="password" defaultValue="admin123" placeholder="Password" className="w-full bg-slate-800 text-white p-3 rounded-lg border border-slate-700"/>
            <button className="w-full bg-indigo-600 hover:bg-indigo-700 text-white p-3 rounded-lg font-semibold">Login</button>
          </form>
          {msg && <p className="text-red-400 text-sm mt-4">{msg}</p>}
          <p className="text-slate-500 text-xs mt-6">Backend must be running at {API_BASE} - Docs at /docs</p>
        </div>
      </div>
    );
  }

  const filtered = compliance.filter(c => 
    (!deptFilter || c.department===deptFilter) &&
    (!search || c.name.toLowerCase().includes(search.toLowerCase()) || c.emp_code.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div><h1 className="font-bold text-lg">Central Attendance - Enterprise</h1><p className="text-xs text-slate-400">Real-time • 3 days / 15 hrs • Empty=Absent</p></div>
          <div className="flex gap-4 items-center">
            <span className="text-sm text-slate-300">{user?.email} ({user?.role})</span>
            <button onClick={()=>{localStorage.clear(); setToken(''); setUser(null)}} className="text-sm bg-slate-800 px-3 py-1 rounded-lg">Logout</button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Today Card */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h2 className="font-semibold mb-4">Today Status - {today?.status || 'loading...'}</h2>
            {today ? (
              <>
                <div className="space-y-2 text-sm">
                  <p className="text-slate-400">Entry: <span className="text-white">{today.entry ? new Date(today.entry).toLocaleString() : 'No entry - ABSENT'}</span></p>
                  <p className="text-slate-400">Exit: <span className="text-white">{today.exit ? new Date(today.exit).toLocaleString() : 'Not exited'}</span></p>
                  <p className="text-slate-400">Present today: <span className="text-white font-bold">{today.present_hours_today ?? 0} hrs</span></p>
                  <p className="text-slate-400">Weekly: <span className="text-white">{today.weekly_total} hrs / {today.days_present_week} days</span></p>
                  <p className="text-slate-400">Needed: <span className="text-amber-400 font-bold">{today.hours_needed_to_achieve_weekly ?? today.hours_needed} hrs</span></p>
                </div>
                <div className="mt-4 p-3 bg-indigo-950/50 border border-indigo-800 rounded-lg text-sm text-indigo-200">{today.message}</div>
                {today.weekly && <div className="mt-3 text-xs text-slate-500">Week {today.weekly.week_start} to {today.weekly.week_end} - Compliant: {today.weekly.is_compliant ? 'YES' : 'NO'}</div>}
              </>
            ) : <p className="text-slate-500">Loading...</p>}

            <div className="mt-6 space-y-3">
              <button disabled={loading} onClick={()=>markAttendance({})} className="w-full bg-white text-black font-bold py-3 rounded-xl hover:bg-slate-200 disabled:opacity-50">
                {today?.entry && !today?.exit ? 'Mark EXIT (Now)' : 'Mark ENTRY (Now)'} 
              </button>
              <button disabled={loading} onClick={markWithLocation} className="w-full bg-slate-800 border border-slate-700 py-3 rounded-xl hover:bg-slate-700">
                📍 Mark with Location (Geofence)
              </button>
            </div>
            {msg && <p className="text-xs mt-3 p-2 bg-slate-800 rounded text-slate-300 break-all">{msg}</p>}
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-semibold mb-3">Test Oct 9 Example (18:26-22:26 = 4 hrs)</h3>
            <div className="space-y-2">
              <input value={manualEntry} onChange={e=>setManualEntry(e.target.value)} className="w-full bg-slate-800 p-2 rounded border border-slate-700 text-sm" placeholder="Entry ISO"/>
              <input value={manualExit} onChange={e=>setManualExit(e.target.value)} className="w-full bg-slate-800 p-2 rounded border border-slate-700 text-sm" placeholder="Exit ISO"/>
              <button onClick={()=>markAttendance({entry_time:manualEntry, exit_time:manualExit})} className="w-full bg-indigo-600 py-2 rounded-lg text-sm font-semibold">Mark 4 hrs (Test)</button>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <h3 className="font-semibold mb-3">Weekly Progress - 15 hrs goal</h3>
            <div className="flex items-center gap-4">
              <div className="w-24 h-24 rounded-full border-8 border-slate-800 flex items-center justify-center relative" style={{borderTopColor: (today?.weekly_total||0)>=15 ? '#10b981' : '#6366f1'}}>
                <span className="font-bold text-xl">{today?.weekly_total||0}/15</span>
              </div>
              <div className="text-sm space-y-1">
                <p>Days: {today?.days_present_week||0} / 3 required</p>
                <p>Hours: {today?.weekly_total||0} / 15 required</p>
                <p className={(today?.weekly_total||0)>=15 && (today?.days_present_week||0)>=3 ? 'text-emerald-400' : 'text-amber-400'}>{(today?.weekly_total||0)>=15 && (today?.days_present_week||0)>=3 ? '✅ COMPLIANT' : '❌ NOT COMPLIANT'}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Compliance Table */}
        <div className="lg:col-span-2">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="font-semibold">Compliance Report - Single API for 10+ people</h2>
              <button onClick={()=>fetchCompliance(token, deptFilter)} className="text-xs bg-slate-800 px-3 py-1 rounded">Refresh</button>
            </div>
            <div className="flex gap-2 mb-4">
              <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search name / emp_code" className="flex-1 bg-slate-800 p-2 rounded border border-slate-700 text-sm"/>
              <select value={deptFilter} onChange={e=>{setDeptFilter(e.target.value); fetchCompliance(token, e.target.value)}} className="bg-slate-800 p-2 rounded border border-slate-700 text-sm">
                <option value="">All Dept</option><option value="IT">IT</option><option value="HR">HR</option><option value="General">General</option>
              </select>
            </div>
            <div className="overflow-auto max-h-[600px]">
              <table className="w-full text-sm">
                <thead className="text-slate-400 sticky top-0 bg-slate-900"><tr><th className="text-left p-2">Emp</th><th className="text-left p-2">Dept</th><th className="p-2">Days</th><th className="p-2">Hours</th><th className="p-2">Deficit</th><th className="p-2">Status</th></tr></thead>
                <tbody>
                  {filtered.map(c=>(
                    <tr key={c.employee_id} className="border-t border-slate-800 hover:bg-slate-800/50">
                      <td className="p-2"><div className="font-medium">{c.name}</div><div className="text-xs text-slate-500">{c.emp_code} - {c.email}</div></td>
                      <td className="p-2 text-slate-400">{c.department}</td>
                      <td className="p-2 text-center">{c.days_present}/3</td>
                      <td className="p-2 text-center">{c.total_hours}/15</td>
                      <td className="p-2 text-center text-amber-400">{c.deficit_days}d / {c.deficit_hours}h</td>
                      <td className="p-2 text-center"><span className={`px-2 py-1 rounded-full text-xs ${c.is_compliant ? 'bg-emerald-900 text-emerald-300' : 'bg-red-900 text-red-300'}`}>{c.is_compliant ? 'Compliant' : 'Non-Compliant'}</span></td>
                    </tr>
                  ))}
                  {filtered.length===0 && <tr><td colSpan={6} className="p-8 text-center text-slate-500">No data - check backend running or login as admin</td></tr>}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-slate-500 mt-3">Policy: 3 days / 15 hrs per week (Mon-Sun). API: POST /api/attendance/reports {`{type:"compliance"}`}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default App;
