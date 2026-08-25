const views = document.querySelectorAll('.view');
const reviewButton = document.querySelector('#review-button');
const submitButton = document.querySelector('#submit-button');
const newOrderButton = document.querySelector('#new-order-button');
const submitError = document.querySelector('#submit-error');
const unitPrice = 180;
let quantity = 1;

function showView(id) {
  views.forEach((view) => view.classList.toggle('active', view.id === id));
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function selectedNoodle() {
  return document.querySelector('input[name="noodle"]:checked').value;
}

function updateQuantity(nextQuantity) {
  quantity = Math.min(99, Math.max(1, nextQuantity));
  const total = unitPrice * quantity;
  document.querySelector('#quantity').textContent = quantity;
  document.querySelector('#menu-total').textContent = `NT$ ${total.toLocaleString('zh-TW')}`;
  document.querySelector('#decrease-quantity').disabled = quantity === 1;
  document.querySelector('#increase-quantity').disabled = quantity === 99;
}

document.querySelector('#decrease-quantity').addEventListener('click', () => updateQuantity(quantity - 1));
document.querySelector('#increase-quantity').addEventListener('click', () => updateQuantity(quantity + 1));

reviewButton.addEventListener('click', () => {
  document.querySelector('#review-noodle').textContent = `麵條：${selectedNoodle()}`;
  document.querySelector('#review-quantity').textContent = `${quantity} 碗`;
  document.querySelector('#review-total').textContent = `NT$ ${(unitPrice * quantity).toLocaleString('zh-TW')}`;
  showView('review-view');
});

document.querySelectorAll('[data-back]').forEach((button) => {
  button.addEventListener('click', () => showView(button.dataset.back));
});

submitButton.addEventListener('click', async () => {
  submitError.textContent = '';
  submitButton.disabled = true;
  submitButton.textContent = '訂單送出中…';

  const order = {
    productId: 'classic-tonkotsu',
    productName: '經典豚骨拉麵',
    noodleFirmness: selectedNoodle(),
    quantity,
    pickupName: document.querySelector('#pickup-name').value.trim(),
    total: unitPrice * quantity,
  };

  try {
    // 下一階段接上 HMI 後台時，提供 window.ORDER_API_URL 即可改用正式 API。
    if (window.ORDER_API_URL) {
      const response = await fetch(window.ORDER_API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(order),
      });
      if (!response.ok) throw new Error('後台目前無法接收訂單');
      const result = await response.json();
      document.querySelector('#order-number').textContent = result.orderNumber;
    } else {
      await new Promise((resolve) => setTimeout(resolve, 500));
      const sequence = Number(localStorage.getItem('ramen-order-sequence') || 0) + 1;
      localStorage.setItem('ramen-order-sequence', sequence);
      localStorage.setItem('ramen-latest-order', JSON.stringify({ ...order, sequence, status: 'waiting' }));
      document.querySelector('#order-number').textContent = `A${String(sequence).padStart(3, '0')}`;
    }
    document.querySelector('#success-quantity').textContent = `本訂單共 ${quantity} 碗`;
    showView('success-view');
  } catch (error) {
    submitError.textContent = `${error.message}，請稍後再試。`;
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = '送出訂單';
  }
});

newOrderButton.addEventListener('click', () => {
  document.querySelector('#pickup-name').value = '';
  document.querySelector('input[value="正常"]').checked = true;
  updateQuantity(1);
  showView('menu-view');
});

updateQuantity(1);
