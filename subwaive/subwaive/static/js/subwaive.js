async function copyElementTextToClipboard(elementId) {
  const element = document.getElementById(elementId);
  if (!element) {
    console.error(`Element with ID '${elementId}' not found.`);
    return;
  }

  const textToCopy = element.textContent; // Or element.value for input/textarea

  try {
    await navigator.clipboard.writeText(textToCopy);
    console.log('Text copied to clipboard successfully!');
  } catch (err) {
    console.error('Failed to copy text: ', err);
    // Fallback for older browsers or if Clipboard API is not available/permitted
    fallbackCopyToClipboard(textToCopy);
  }
}

// Fallback function for older browsers or if Clipboard API fails
function fallbackCopyToClipboard(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'absolute';
  textarea.style.left = '-9999px'; // Hide the textarea off-screen
  document.body.appendChild(textarea);
  textarea.select();
  try {
    document.execCommand('copy');
    console.log('Text copied using execCommand (fallback).');
  } catch (err) {
    console.error('Failed to copy text using execCommand: ', err);
  } finally {
    document.body.removeChild(textarea);
  }
}