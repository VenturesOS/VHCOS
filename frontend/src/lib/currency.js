/**
 * Currency utilities for VHC Talent OS
 * Default currency: INR (Indian Rupee)
 * Phase-1: Single currency (INR only)
 */

/**
 * Format number in Indian numbering style
 * Example: 500000 -> 5,00,000
 * @param {number} num - Number to format
 * @returns {string} Formatted number string
 */
export function formatIndianNumber(num) {
  if (num === null || num === undefined) return '';
  
  const numStr = Math.round(num).toString();
  
  // For numbers less than 1000, no formatting needed
  if (numStr.length <= 3) return numStr;
  
  // Indian number format: last 3 digits, then pairs
  let lastThree = numStr.slice(-3);
  let remaining = numStr.slice(0, -3);
  
  // Add commas every 2 digits for remaining part
  if (remaining.length > 0) {
    remaining = remaining.replace(/\B(?=(\d{2})+(?!\d))/g, ',');
  }
  
  return remaining ? `${remaining},${lastThree}` : lastThree;
}

/**
 * Format salary in INR
 * @param {number} amount - Salary amount
 * @param {boolean} showSymbol - Whether to show ₹ symbol (default: true)
 * @returns {string} Formatted salary string
 */
export function formatSalaryINR(amount, showSymbol = true) {
  if (amount === null || amount === undefined) return '';
  
  const formatted = formatIndianNumber(amount);
  return showSymbol ? `₹${formatted}` : formatted;
}

/**
 * Format salary range in INR
 * @param {number|null} min - Minimum salary
 * @param {number|null} max - Maximum salary
 * @returns {string} Formatted salary range string
 */
export function formatSalaryRangeINR(min, max) {
  if (!min && !max) return 'Not specified';
  
  if (min && max) {
    return `₹${formatIndianNumber(min)} - ₹${formatIndianNumber(max)}`;
  }
  
  if (min) return `₹${formatIndianNumber(min)}+`;
  if (max) return `Up to ₹${formatIndianNumber(max)}`;
  
  return 'Not specified';
}

/**
 * Format salary for display with LPA conversion if applicable
 * @param {number|null} min - Minimum salary
 * @param {number|null} max - Maximum salary  
 * @returns {string} Formatted salary string with LPA if >= 100000
 */
export function formatSalaryDisplay(min, max) {
  if (!min && !max) return 'Not disclosed';
  
  // Convert to LPA (Lakhs Per Annum) if >= 100000
  const toLPA = (amount) => {
    if (amount >= 100000) {
      const lpa = amount / 100000;
      return lpa % 1 === 0 ? `${lpa} LPA` : `${lpa.toFixed(1)} LPA`;
    }
    return `₹${formatIndianNumber(amount)}`;
  };
  
  if (min && max) {
    return `${toLPA(min)} - ${toLPA(max)}`;
  }
  
  if (min) return `${toLPA(min)}+`;
  if (max) return `Up to ${toLPA(max)}`;
  
  return 'Not disclosed';
}

// Default currency code for Phase-1
export const DEFAULT_CURRENCY = 'INR';
export const CURRENCY_SYMBOL = '₹';

// Alias for convenience
export const formatINR = formatSalaryINR;
