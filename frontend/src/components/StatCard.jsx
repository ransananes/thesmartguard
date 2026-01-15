import React from 'react';
import PropTypes from 'prop-types';

const StatCard = ({ label, value, icon: Icon }) => {
    return (
        <div className="bg-neutral-800/50 rounded-xl p-4 border border-white/5 backdrop-blur-sm">
            <Icon className="w-5 h-5 text-neutral-400 mb-2" />
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-neutral-500 uppercase tracking-widest">{label}</div>
        </div>
    );
};

StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.string.isRequired,
    icon: PropTypes.elementType.isRequired,
};

export default StatCard;
