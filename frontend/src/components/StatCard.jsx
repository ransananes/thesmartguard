import React from 'react';
import PropTypes from 'prop-types';

const StatCard = ({ label, value, icon: Icon }) => {
    return (
        <div className="glass-card p-5 group hover:border-purple-500/50 transition-all duration-300 hover:-translate-y-1">
            <div className="flex items-center justify-between mb-3">
                <div className="p-2 bg-purple-500/10 rounded-lg group-hover:bg-purple-500/20 transition-colors">
                    <Icon className="w-5 h-5 text-purple-400" />
                </div>
                <div className="w-1.5 h-1.5 rounded-full bg-purple-500/50 group-hover:bg-purple-500 animate-pulse" />
            </div>
            <div className="text-3xl font-bold tracking-tight mb-1">{value}</div>
            <div className="text-[10px] text-neutral-500 font-bold uppercase tracking-[0.2em]">{label}</div>
        </div>
    );
};

StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.string.isRequired,
    icon: PropTypes.elementType.isRequired,
};

export default StatCard;
