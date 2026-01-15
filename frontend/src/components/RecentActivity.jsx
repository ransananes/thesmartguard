import React from 'react';

const RecentActivity = () => {
    return (
        <div className="relative z-10 w-full mt-8 text-left">
            <h3 className="text-xs font-bold text-neutral-500 tracking-widest uppercase mb-4 border-b border-white/5 pb-2">Recent Events</h3>
            <div className="space-y-3">
                {[1, 2, 3].map((_, i) => (
                    <div key={i} className="flex items-center gap-3 text-sm text-neutral-300 opacity-60">
                        <div className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
                        <span>Motion detected at Gate A</span>
                        <span className="ml-auto text-xs font-mono text-neutral-600">10:42:0{i}</span>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default RecentActivity;
