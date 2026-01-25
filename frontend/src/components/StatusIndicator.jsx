import React from 'react';
import PropTypes from 'prop-types';
import { Activity, Lock, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { SYSTEM_STATUS, STATUS_CONFIG } from '../constants';
import RecentActivity from './RecentActivity';

const StatusIndicator = ({ status }) => {
    const config = STATUS_CONFIG[status];
    const cn = (...inputs) => twMerge(clsx(inputs));

    return (
        <div className={cn(
            "h-full rounded-2xl p-6 border transition-all duration-500 flex flex-col items-center justify-center text-center gap-6 relative overflow-hidden",
            config.borderColor,
            config.bgColor
        )}>
            <div className={cn("absolute inset-0 opacity-20 blur-3xl", config.bgColor.replace('/10', '/30').replace('/20', '/40'))} />

            <div className={cn("relative z-10 w-24 h-24 rounded-full flex items-center justify-center border-4 backdrop-blur-md shadow-[0_0_30px_rgba(0,0,0,0.3)]", config.borderColor)}>
                {status === SYSTEM_STATUS.SCANNING && <Activity size={40} color={config.iconColor} className="animate-spin-slow" />}
                {status === SYSTEM_STATUS.ACCESS_GRANTED && <Lock size={40} color={config.iconColor} />}
                {status === SYSTEM_STATUS.INTRUDER_ALERT && <AlertTriangle size={40} color={config.iconColor} className="animate-bounce" />}
            </div>

            <div className="relative z-10 space-y-2">
                <h2 className="text-sm font-bold text-neutral-400 tracking-[0.2em] uppercase">Current Status</h2>
                <div className={cn("text-3xl font-black uppercase tracking-wider transition-colors duration-300", config.color)}>
                    {config.label}
                </div>
            </div>

            <RecentActivity />
        </div>
    );
};

StatusIndicator.propTypes = {
    status: PropTypes.oneOf(Object.values(SYSTEM_STATUS)).isRequired,
};

export default StatusIndicator;
