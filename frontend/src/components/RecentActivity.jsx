import React, { useState, useEffect } from 'react';
import { api } from '../services/api';

const RecentActivity = () => {
    const [activities, setActivities] = useState([]);
    
    useEffect(() => {
        const fetchHistory = async () => {
            try {
                const data = await api.fetchDetectionHistory();
                if (data.success) {
                    setActivities(data.history);
                }
            } catch (error) {
                console.error("Failed to load history:", error);
            }
        };

        fetchHistory();
        
        const interval = setInterval(fetchHistory, 15000);
        return () => clearInterval(interval);
    }, []);

    const formatTime = (isoString) => {
        if (!isoString) return '';
        const date = new Date(isoString + 'Z'); 
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    };

    return (
        <div className="relative z-10 w-full text-left h-full">
            <h3 className="text-xs font-bold text-neutral-500 tracking-widest uppercase mb-4 border-b border-white/5 pb-2 sticky top-0 bg-neutral-900/90 backdrop-blur-sm">Recent Events</h3>
            <div className="space-y-3 pb-4">
                {activities.length === 0 ? (
                     <div className="text-sm text-neutral-500 italic">No recent detections found.</div>
                ) : (
                    activities.map((item, i) => (
                        <div key={item.id || i} className="flex items-center gap-3 text-sm text-neutral-300 opacity-80 hover:opacity-100 transition-opacity">
                            <div className="w-1.5 h-1.5 rounded-full bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.5)]" />
                            <span className="font-medium">{item.label}</span>
                            <span className="ml-auto text-xs font-mono text-neutral-500">{formatTime(item.timestamp)}</span>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

export default RecentActivity;
